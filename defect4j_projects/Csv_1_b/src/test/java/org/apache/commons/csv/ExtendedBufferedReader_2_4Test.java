package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.BufferedReader;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;

import java.io.IOException;
import java.io.Reader;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class ExtendedBufferedReader_2_4Test {

    ExtendedBufferedReader extendedBufferedReader;
    Reader mockReader;

    @BeforeEach
    void setUp() {
        mockReader = mock(Reader.class);
        extendedBufferedReader = new ExtendedBufferedReader(mockReader);
    }

    @Test
    @Timeout(8000)
    void testReadReturnsCharAndUpdatesLastCharWithoutLineIncrement() throws IOException {
        ExtendedBufferedReader br = new ExtendedBufferedReader(mockReader) {
            int callCount = 0;

            @Override
            public int read() throws IOException {
                callCount++;
                int current;
                if (callCount == 1) {
                    current = 'A'; // Not a newline
                } else if (callCount == 2) {
                    current = '\n'; // Newline
                } else if (callCount == 3) {
                    current = END_OF_STREAM; // End of stream
                } else {
                    current = END_OF_STREAM;
                }

                // Use reflection to update private fields
                try {
                    java.lang.reflect.Field lineCounterField = ExtendedBufferedReader.class.getDeclaredField("lineCounter");
                    lineCounterField.setAccessible(true);
                    int lineCounter = lineCounterField.getInt(this);
                    if (current == '\n') {
                        lineCounter++;
                        lineCounterField.setInt(this, lineCounter);
                    }
                    java.lang.reflect.Field lastCharField = ExtendedBufferedReader.class.getDeclaredField("lastChar");
                    lastCharField.setAccessible(true);
                    lastCharField.setInt(this, current);
                } catch (Exception e) {
                    throw new RuntimeException(e);
                }

                return current;
            }
        };

        // First call with 'A'
        int result1 = br.read();
        assertEquals('A', result1);

        int lineNumberField1 = getPrivateIntField(br, "lineCounter");
        assertEquals(0, lineNumberField1);

        int lastCharField1 = getPrivateIntField(br, "lastChar");
        assertEquals('A', lastCharField1);

        // Second call with '\n'
        int result2 = br.read();
        assertEquals('\n', result2);

        int lineNumberField2 = getPrivateIntField(br, "lineCounter");
        assertEquals(1, lineNumberField2);

        int lastCharField2 = getPrivateIntField(br, "lastChar");
        assertEquals('\n', lastCharField2);

        // Third call with END_OF_STREAM
        int result3 = br.read();
        assertEquals(ExtendedBufferedReader.END_OF_STREAM, result3);

        int lineNumberField3 = getPrivateIntField(br, "lineCounter");
        assertEquals(1, lineNumberField3);

        int lastCharField3 = getPrivateIntField(br, "lastChar");
        assertEquals(ExtendedBufferedReader.END_OF_STREAM, lastCharField3);
    }

    private int getPrivateIntField(Object instance, String fieldName) {
        try {
            java.lang.reflect.Field field = ExtendedBufferedReader.class.getDeclaredField(fieldName);
            field.setAccessible(true);
            return field.getInt(instance);
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }
}