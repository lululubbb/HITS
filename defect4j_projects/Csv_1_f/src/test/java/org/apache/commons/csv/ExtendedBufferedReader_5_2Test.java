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

class ExtendedBufferedReader_5_2Test {

    ExtendedBufferedReader extendedBufferedReader;
    Reader mockReader;

    @BeforeEach
    void setUp() {
        mockReader = mock(Reader.class);
        extendedBufferedReader = new ExtendedBufferedReader(mockReader);
    }

    @Test
    @Timeout(8000)
    void testReadLine_NullLine() throws IOException, NoSuchFieldException, IllegalAccessException {
        // Mock the underlying Reader to cause BufferedReader.readLine() to return null
        when(mockReader.read(any(char[].class), anyInt(), anyInt())).thenReturn(-1);

        ExtendedBufferedReader reader = new ExtendedBufferedReader(mockReader);

        String result = reader.readLine();
        assertNull(result);

        Field lastCharField = ExtendedBufferedReader.class.getDeclaredField("lastChar");
        lastCharField.setAccessible(true);
        int lastCharValue = lastCharField.getInt(reader);
        assertEquals(ExtendedBufferedReader.END_OF_STREAM, lastCharValue);

        Field lineCounterField = ExtendedBufferedReader.class.getDeclaredField("lineCounter");
        lineCounterField.setAccessible(true);
        int lineCounterValue = lineCounterField.getInt(reader);
        assertEquals(0, lineCounterValue);
    }

    @Test
    @Timeout(8000)
    void testReadLine_EmptyLine() throws IOException, NoSuchFieldException, IllegalAccessException {
        // Mock the underlying Reader to return an empty line (only newline character)
        when(mockReader.read(any(char[].class), anyInt(), anyInt())).thenAnswer(invocation -> {
            char[] buf = invocation.getArgument(0);
            int off = invocation.getArgument(1);
            buf[off] = '\n';
            return 1;
        });

        ExtendedBufferedReader reader = new ExtendedBufferedReader(mockReader);

        String result = reader.readLine();
        assertEquals("", result);

        Field lastCharField = ExtendedBufferedReader.class.getDeclaredField("lastChar");
        lastCharField.setAccessible(true);
        int lastCharValue = lastCharField.getInt(reader);
        assertEquals(ExtendedBufferedReader.UNDEFINED, lastCharValue);

        Field lineCounterField = ExtendedBufferedReader.class.getDeclaredField("lineCounter");
        lineCounterField.setAccessible(true);
        int lineCounterValue = lineCounterField.getInt(reader);
        assertEquals(1, lineCounterValue);
    }

    @Test
    @Timeout(8000)
    void testReadLine_NonEmptyLine() throws IOException, NoSuchFieldException, IllegalAccessException {
        String testLine = "Hello, World!";

        // Mock the underlying Reader to return the testLine followed by newline
        when(mockReader.read(any(char[].class), anyInt(), anyInt())).thenAnswer(new org.mockito.stubbing.Answer<Integer>() {
            private int pos = 0;
            private final char[] chars = (testLine + "\n").toCharArray();

            @Override
            public Integer answer(org.mockito.invocation.InvocationOnMock invocation) {
                char[] buf = invocation.getArgument(0);
                int off = invocation.getArgument(1);
                int len = invocation.getArgument(2);
                if (pos >= chars.length) {
                    return -1;
                }
                int readCount = 0;
                for (int i = 0; i < len && pos < chars.length; i++, pos++) {
                    buf[off + i] = chars[pos];
                    readCount++;
                }
                return readCount;
            }
        });

        ExtendedBufferedReader reader = new ExtendedBufferedReader(mockReader);

        String result = reader.readLine();
        assertEquals(testLine, result);

        Field lastCharField = ExtendedBufferedReader.class.getDeclaredField("lastChar");
        lastCharField.setAccessible(true);
        int lastCharValue = lastCharField.getInt(reader);
        assertEquals(testLine.charAt(testLine.length() - 1), lastCharValue);

        Field lineCounterField = ExtendedBufferedReader.class.getDeclaredField("lineCounter");
        lineCounterField.setAccessible(true);
        int lineCounterValue = lineCounterField.getInt(reader);
        assertEquals(1, lineCounterValue);
    }
}