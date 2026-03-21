package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.BufferedReader;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.io.IOException;
import java.io.Reader;
import java.lang.reflect.Field;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class ExtendedBufferedReader_4_5Test {

    ExtendedBufferedReader extendedBufferedReader;
    Reader mockReader;

    @BeforeEach
    void setUp() {
        mockReader = mock(Reader.class);
        extendedBufferedReader = new ExtendedBufferedReader(mockReader) {
            // Override read(char[], int, int) to call super.read from BufferedReader
            @Override
            public int read(char[] buf, int offset, int length) throws IOException {
                return super.read(buf, offset, length);
            }
        };
    }

    // Helper to set private field lastChar on the instance extendedBufferedReader
    private void setLastChar(int value) throws Exception {
        Field lastCharField = ExtendedBufferedReader.class.getDeclaredField("lastChar");
        lastCharField.setAccessible(true);
        lastCharField.setInt(extendedBufferedReader, value);
    }

    // Helper to get private field lastChar on the instance extendedBufferedReader
    private int getLastChar() throws Exception {
        Field lastCharField = ExtendedBufferedReader.class.getDeclaredField("lastChar");
        lastCharField.setAccessible(true);
        return lastCharField.getInt(extendedBufferedReader);
    }

    // Helper to get private field lineCounter on the instance extendedBufferedReader
    private int getLineCounter() throws Exception {
        Field lineCounterField = ExtendedBufferedReader.class.getDeclaredField("lineCounter");
        lineCounterField.setAccessible(true);
        return lineCounterField.getInt(extendedBufferedReader);
    }

    @Test
    @Timeout(8000)
    void testReadLengthZeroReturnsZero() throws IOException {
        char[] buf = new char[10];
        int result = extendedBufferedReader.read(buf, 0, 0);
        assertEquals(0, result);
    }

    @Test
    @Timeout(8000)
    void testReadReturnsMinusOneSetsLastCharToEndOfStream() throws Exception {
        char[] buf = new char[10];

        Reader mockedReader = mock(Reader.class);
        doReturn(-1).when(mockedReader).read(any(char[].class), anyInt(), anyInt());
        ExtendedBufferedReader reader = new ExtendedBufferedReader(mockedReader);

        int result = reader.read(buf, 0, 5);

        assertEquals(-1, result);

        Field lastCharField = ExtendedBufferedReader.class.getDeclaredField("lastChar");
        lastCharField.setAccessible(true);
        int lastCharValue = lastCharField.getInt(reader);
        assertEquals(ExtendedBufferedReader.END_OF_STREAM, lastCharValue);
    }

    @Test
    @Timeout(8000)
    void testReadWithNewlineNotPrecededByCarriageReturnIncrementsLineCounter() throws Exception {
        // buf contains chars: a \n b
        char[] buf = new char[]{'a', '\n', 'b'};

        Reader mockedReader = mock(Reader.class);
        doAnswer(invocation -> {
            char[] array = invocation.getArgument(0);
            int offset = invocation.getArgument(1);
            int length = invocation.getArgument(2);
            System.arraycopy(buf, 0, array, offset, 3);
            return 3;
        }).when(mockedReader).read(any(char[].class), eq(0), eq(3));

        ExtendedBufferedReader reader = new ExtendedBufferedReader(mockedReader);

        setLastChar(reader, ExtendedBufferedReader.UNDEFINED);

        int len = reader.read(buf, 0, 3);

        assertEquals(3, len);

        int lineCounter = getLineCounter(reader);
        assertEquals(1, lineCounter);

        int lastChar = getLastChar(reader);
        assertEquals('b', lastChar);
    }

    @Test
    @Timeout(8000)
    void testReadWithNewlinePrecededByCarriageReturnDoesNotIncrementLineCounter() throws Exception {
        // buf contains chars: \r \n
        char[] buf = new char[]{'\r', '\n'};

        Reader mockedReader = mock(Reader.class);
        doAnswer(invocation -> {
            char[] array = invocation.getArgument(0);
            int offset = invocation.getArgument(1);
            int length = invocation.getArgument(2);
            System.arraycopy(buf, 0, array, offset, 2);
            return 2;
        }).when(mockedReader).read(any(char[].class), eq(0), eq(2));

        ExtendedBufferedReader reader = new ExtendedBufferedReader(mockedReader);

        setLastChar(reader, ExtendedBufferedReader.UNDEFINED);

        int len = reader.read(buf, 0, 2);

        assertEquals(2, len);
        int lineCounter = getLineCounter(reader);
        assertEquals(1, lineCounter);

        int lastChar = getLastChar(reader);
        assertEquals('\n', lastChar);
    }

    @Test
    @Timeout(8000)
    void testReadWithCarriageReturnIncrementsLineCounter() throws Exception {
        // buf contains chars: a \r b
        char[] buf = new char[]{'a', '\r', 'b'};

        Reader mockedReader = mock(Reader.class);
        doAnswer(invocation -> {
            char[] array = invocation.getArgument(0);
            int offset = invocation.getArgument(1);
            int length = invocation.getArgument(2);
            System.arraycopy(buf, 0, array, offset, 3);
            return 3;
        }).when(mockedReader).read(any(char[].class), eq(0), eq(3));

        ExtendedBufferedReader reader = new ExtendedBufferedReader(mockedReader);

        setLastChar(reader, ExtendedBufferedReader.UNDEFINED);

        int len = reader.read(buf, 0, 3);

        assertEquals(3, len);

        int lineCounter = getLineCounter(reader);
        assertEquals(1, lineCounter);

        int lastChar = getLastChar(reader);
        assertEquals('b', lastChar);
    }

    @Test
    @Timeout(8000)
    void testReadWithOffsetNonZero() throws Exception {
        // buf contains: x x \n a b
        char[] buf = new char[]{'x', 'x', '\n', 'a', 'b'};

        Reader mockedReader = mock(Reader.class);
        doAnswer(invocation -> {
            char[] array = invocation.getArgument(0);
            int offset = invocation.getArgument(1);
            int length = invocation.getArgument(2);
            // copy 3 chars starting at buf[1] into array at offset
            System.arraycopy(buf, 1, array, offset, 3);
            return 3;
        }).when(mockedReader).read(any(char[].class), eq(1), eq(3));

        ExtendedBufferedReader reader = new ExtendedBufferedReader(mockedReader);

        setLastChar(reader, ExtendedBufferedReader.UNDEFINED);

        int len = reader.read(buf, 1, 3);

        assertEquals(3, len);

        int lineCounter = getLineCounter(reader);
        assertEquals(1, lineCounter);

        int lastChar = getLastChar(reader);
        assertEquals('a', lastChar);
    }

    // Helper methods to access private fields on given ExtendedBufferedReader instance

    private void setLastChar(ExtendedBufferedReader reader, int value) throws Exception {
        Field lastCharField = ExtendedBufferedReader.class.getDeclaredField("lastChar");
        lastCharField.setAccessible(true);
        lastCharField.setInt(reader, value);
    }

    private int getLastChar(ExtendedBufferedReader reader) throws Exception {
        Field lastCharField = ExtendedBufferedReader.class.getDeclaredField("lastChar");
        lastCharField.setAccessible(true);
        return lastCharField.getInt(reader);
    }

    private int getLineCounter(ExtendedBufferedReader reader) throws Exception {
        Field lineCounterField = ExtendedBufferedReader.class.getDeclaredField("lineCounter");
        lineCounterField.setAccessible(true);
        return lineCounterField.getInt(reader);
    }
}