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

class ExtendedBufferedReader_4_4Test {

    private ExtendedBufferedReader extendedBufferedReader;
    private Reader mockReader;

    @BeforeEach
    void setUp() {
        mockReader = mock(Reader.class);
        extendedBufferedReader = new ExtendedBufferedReader(mockReader) {
            // Override read(char[], int, int) to call super.read(char[], int, int)
            @Override
            public int read(char[] buf, int offset, int length) throws IOException {
                return super.read(buf, offset, length);
            }
        };
    }

    @Test
    @Timeout(8000)
    void testReadLengthZeroReturnsZero() throws IOException {
        char[] buffer = new char[10];
        int result = extendedBufferedReader.read(buffer, 0, 0);
        assertEquals(0, result);
    }

    @Test
    @Timeout(8000)
    void testReadReturnsMinusOneSetsLastCharToEndOfStream() throws IOException {
        char[] buffer = new char[10];

        // Mock underlying Reader to return -1
        doReturn(-1).when(mockReader).read(any(char[].class), anyInt(), anyInt());

        int result = extendedBufferedReader.read(buffer, 0, 5);
        assertEquals(-1, result);

        int lastChar = getPrivateIntField(extendedBufferedReader, "lastChar");
        assertEquals(ExtendedBufferedReader.END_OF_STREAM, lastChar);
    }

    @Test
    @Timeout(8000)
    void testReadWithNoNewlineOrCarriageReturnInBuffer() throws IOException {
        char[] buffer = new char[5];
        buffer[0] = 'a';
        buffer[1] = 'b';
        buffer[2] = 'c';
        buffer[3] = 'd';
        buffer[4] = 'e';

        // Mock underlying Reader to copy buffer and return length
        doAnswer(invocation -> {
            char[] buf = invocation.getArgument(0);
            int off = invocation.getArgument(1);
            int len = invocation.getArgument(2);
            System.arraycopy(buffer, 0, buf, off, len);
            return len;
        }).when(mockReader).read(any(char[].class), anyInt(), anyInt());

        char[] readBuffer = new char[5];
        int result = extendedBufferedReader.read(readBuffer, 0, 5);
        assertEquals(5, result);

        int lineCounter = getPrivateIntField(extendedBufferedReader, "lineCounter");
        assertEquals(0, lineCounter);

        int lastChar = getPrivateIntField(extendedBufferedReader, "lastChar");
        assertEquals('e', lastChar);
    }

    @Test
    @Timeout(8000)
    void testReadWithNewlineNotPrecededByCarriageReturnInBuffer() throws IOException {
        char[] buffer = new char[]{'a', '\n', 'b', 'c', 'd'};

        doAnswer(invocation -> {
            char[] buf = invocation.getArgument(0);
            int off = invocation.getArgument(1);
            int len = invocation.getArgument(2);
            System.arraycopy(buffer, 0, buf, off, len);
            return len;
        }).when(mockReader).read(any(char[].class), anyInt(), anyInt());

        char[] readBuffer = new char[5];
        int result = extendedBufferedReader.read(readBuffer, 0, 5);
        assertEquals(5, result);

        int lineCounter = getPrivateIntField(extendedBufferedReader, "lineCounter");
        assertEquals(1, lineCounter);

        int lastChar = getPrivateIntField(extendedBufferedReader, "lastChar");
        assertEquals('d', lastChar);
    }

    @Test
    @Timeout(8000)
    void testReadWithNewlinePrecededByCarriageReturnInBuffer() throws IOException {
        char[] buffer = new char[]{'a', '\r', '\n', 'b', 'c'};

        doAnswer(invocation -> {
            char[] buf = invocation.getArgument(0);
            int off = invocation.getArgument(1);
            int len = invocation.getArgument(2);
            System.arraycopy(buffer, 0, buf, off, len);
            return len;
        }).when(mockReader).read(any(char[].class), anyInt(), anyInt());

        char[] readBuffer = new char[5];
        int result = extendedBufferedReader.read(readBuffer, 0, 5);
        assertEquals(5, result);

        int lineCounter = getPrivateIntField(extendedBufferedReader, "lineCounter");
        assertEquals(1, lineCounter);

        int lastChar = getPrivateIntField(extendedBufferedReader, "lastChar");
        assertEquals('c', lastChar);
    }

    @Test
    @Timeout(8000)
    void testReadWithNewlineAtZeroIndexAndLastCharNotCarriageReturn() throws IOException {
        char[] buffer = new char[]{'\n', 'a', 'b', 'c', 'd'};

        doAnswer(invocation -> {
            char[] buf = invocation.getArgument(0);
            int off = invocation.getArgument(1);
            int len = invocation.getArgument(2);
            System.arraycopy(buffer, 0, buf, off, len);
            return len;
        }).when(mockReader).read(any(char[].class), anyInt(), anyInt());

        setPrivateIntField(extendedBufferedReader, "lastChar", 'x');

        char[] readBuffer = new char[5];
        int result = extendedBufferedReader.read(readBuffer, 0, 5);
        assertEquals(5, result);

        int lineCounter = getPrivateIntField(extendedBufferedReader, "lineCounter");
        assertEquals(1, lineCounter);

        int lastChar = getPrivateIntField(extendedBufferedReader, "lastChar");
        assertEquals('d', lastChar);
    }

    @Test
    @Timeout(8000)
    void testReadWithNewlineAtZeroIndexAndLastCharIsCarriageReturn() throws IOException {
        char[] buffer = new char[]{'\n', 'a', 'b', 'c', 'd'};

        doAnswer(invocation -> {
            char[] buf = invocation.getArgument(0);
            int off = invocation.getArgument(1);
            int len = invocation.getArgument(2);
            System.arraycopy(buffer, 0, buf, off, len);
            return len;
        }).when(mockReader).read(any(char[].class), anyInt(), anyInt());

        setPrivateIntField(extendedBufferedReader, "lastChar", '\r');

        char[] readBuffer = new char[5];
        int result = extendedBufferedReader.read(readBuffer, 0, 5);
        assertEquals(5, result);

        int lineCounter = getPrivateIntField(extendedBufferedReader, "lineCounter");
        assertEquals(0, lineCounter);

        int lastChar = getPrivateIntField(extendedBufferedReader, "lastChar");
        assertEquals('d', lastChar);
    }

    private int getPrivateIntField(Object instance, String fieldName) {
        try {
            Field field = ExtendedBufferedReader.class.getDeclaredField(fieldName);
            field.setAccessible(true);
            return field.getInt(instance);
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

    private void setPrivateIntField(Object instance, String fieldName, int value) {
        try {
            Field field = ExtendedBufferedReader.class.getDeclaredField(fieldName);
            field.setAccessible(true);
            field.setInt(instance, value);
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }
}